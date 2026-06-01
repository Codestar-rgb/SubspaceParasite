package com.srp.client.renderer;

import com.srp.client.model.InhooModel;
import com.srp.entity.InhooEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InhooRenderer extends GeoEntityRenderer<InhooEntity> {

    public InhooRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InhooModel());
    }
}
