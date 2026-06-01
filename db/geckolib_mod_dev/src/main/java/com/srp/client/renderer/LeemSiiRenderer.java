package com.srp.client.renderer;

import com.srp.client.model.LeemSiiModel;
import com.srp.entity.LeemSiiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeemSiiRenderer extends GeoEntityRenderer<LeemSiiEntity> {

    public LeemSiiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeemSiiModel());
    }
}
