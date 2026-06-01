package com.srp.client.renderer;

import com.srp.client.model.LeerModel;
import com.srp.entity.LeerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeerRenderer extends GeoEntityRenderer<LeerEntity> {

    public LeerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeerModel());
    }
}
